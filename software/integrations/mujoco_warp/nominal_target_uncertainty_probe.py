"""Exploratory MuJoCo Warp propagation of separated joint-error sources."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import platform
import subprocess
from pathlib import Path
from typing import Any


EXPECTED = {
    "pose_bundle": "388ca38f7d86569381c1e1c4abd25b129a571310f8fc9712529a61006a2f7385",
    "target_catalog": "6779213e832ab27eeda1e7fb245f57ff8cb0d56707b5aa73a8f31ec483a620f2",
    "virtual_profile": "38b348ace299140e5908cf367fc15f32b33bebe9b064d5efffe5dcf95f7b4634",
    "mjcf": "448b711ae30ed3df8a5f5eff66ecb53034f6540eade7264388d86e3911a7a8a0",
}
LEVELS_RAD = [0.00025, 0.0005, 0.001, 0.002, 0.004, 0.008]
REFINEMENT_LEVELS_RAD = {
    "random_joint_noise": [
        0.00025,
        0.002,
        0.00225,
        0.0025,
        0.00275,
        0.003,
        0.00325,
        0.0035,
        0.00375,
        0.004,
    ],
    "approach_direction_backlash": [
        0.008,
        0.01,
        0.012,
        0.014,
        0.016,
        0.02,
        0.024,
        0.032,
    ],
    "systematic_calibration_offset": [
        0.008,
        0.01,
        0.012,
        0.014,
        0.016,
        0.02,
        0.024,
        0.032,
    ],
}
FEASIBILITY_HALF_WIDTHS_MM = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
FEASIBILITY_NOISE_LEVELS_RAD = [
    0.0,
    0.00025,
    0.0005,
    0.001,
    0.0015,
    0.002,
    0.00225,
    0.0025,
    0.00275,
    0.003,
    0.00325,
    0.0035,
    0.00375,
    0.004,
]
FEASIBILITY_BACKLASH_LEVELS_RAD = [0.0, 0.002, 0.004, 0.006, 0.008]
FEASIBILITY_SYSTEMATIC_LEVELS_RAD = [0.0, 0.002, 0.004, 0.006, 0.008]
CALIBRATED_HALF_WIDTHS_MM = [3.0, 4.0]
CALIBRATED_RANDOM_LEVELS_RAD = [0.001, 0.0015, 0.002]
CALIBRATED_FIXED_SOURCE_MAGNITUDES_RAD = [0.002, 0.004, 0.008]
CALIBRATED_RESIDUAL_FRACTIONS = [0.0, 0.1, 0.25, 0.5, 1.0]
WORLDS_PER_TARGET = 4096
TARGET_COUNT = 46
SEED = 2_026_100_301
MISS_UCB_LIMIT = 0.001
JACOBIAN_RATIO_RANGE = (0.8, 1.2)
FINITE_DIFFERENCE_STEP_RAD = 1e-5
ONE_SIDED_95_Z = 1.6448536269514722


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
        "utf-8"
    )


def _wilson_upper(successes: int, total: int) -> float:
    proportion = successes / total
    z2 = ONE_SIDED_95_Z**2
    center = proportion + z2 / (2.0 * total)
    spread = ONE_SIDED_95_Z * math.sqrt(
        proportion * (1.0 - proportion) / total + z2 / (4.0 * total * total)
    )
    return (center + spread) / (1.0 + z2 / total)


def _score_absolute_target_rectangles(tips_xy, centers_xy, half_extents_xy, np):
    """Score absolute board-frame landings without per-source recentering."""
    delta_center = tips_xy - centers_xy[:, None, :]
    margins = np.minimum(
        half_extents_xy[:, None, 0] - np.abs(delta_center[:, :, 0]),
        half_extents_xy[:, None, 1] - np.abs(delta_center[:, :, 1]),
    )
    return delta_center, margins, margins < 0.0


def _stack(device: str) -> dict[str, Any]:
    completed = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=index,uuid,name,driver_version,compute_cap",
            "--format=csv,noheader,nounits",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    gpus = []
    for line in completed.stdout.splitlines():
        if line.strip():
            index, uuid, name, driver, capability = (
                part.strip() for part in line.split(",", 4)
            )
            gpus.append(
                {
                    "index": int(index),
                    "uuid": uuid,
                    "name": name,
                    "driver_version": driver,
                    "compute_capability": capability,
                }
            )
    index = int(device.split(":", 1)[1])
    return {
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "packages": {
            name: importlib.metadata.version(name)
            for name in ("mujoco", "mujoco-warp", "numpy", "warp-lang")
        },
        "selected_gpu": gpus[index],
    }


def _validate_pose_bundle(bundle: dict[str, Any]) -> None:
    if (
        bundle.get("schema") != "rocell.mujoco_warp_nominal_target_pose_bundle.v1"
        or bundle.get("status") != "PASS_EXPLORATORY_POSE_SOURCE"
        or bundle.get("scope") != "SYNTHETIC_UNMEASURED_RANK1_KEYBOARD_CONTACTS_ONLY"
        or bundle.get("target_count") != TARGET_COUNT
        or len(bundle.get("poses", [])) != TARGET_COUNT
    ):
        raise ValueError("unsupported nominal target pose bundle")
    unsigned = dict(bundle)
    claimed = unsigned.pop("receipt_sha256", None)
    if claimed != hashlib.sha256(canonical_bytes(unsigned)).hexdigest():
        raise ValueError("pose bundle canonical receipt mismatch")
    target_ids = [pose.get("target_id") for pose in bundle["poses"]]
    if target_ids != sorted(target_ids) or len(set(target_ids)) != TARGET_COUNT:
        raise ValueError("pose target identities/order changed")
    if bundle.get("hardware_access") is not False or bundle.get("physical_authority") is not False:
        raise ValueError("pose bundle carries authority")
    if bundle.get("hardware_write_count") != 0 or bundle.get("physical_movement_count") != 0:
        raise ValueError("pose bundle records physical activity")


def _board_tips(data, hand_id: int, board_t_world, tool_length_mm: float, np):
    positions = np.asarray(data.xpos.numpy(), dtype=np.float64)[:, hand_id, :] * 1000.0
    rotations = np.asarray(data.xmat.numpy(), dtype=np.float64)[:, hand_id, :, :]
    offsets = rotations @ np.asarray([0.0, 0.0, -tool_length_mm], dtype=np.float64)
    world = positions + offsets
    homogeneous = np.concatenate((world, np.ones((world.shape[0], 1))), axis=1)
    return (board_t_world @ homogeneous.T).T[:, :3]


def _safe_width_cells(tips, centers, poses, np, half_widths=None):
    cells = []
    for half_width_mm in half_widths or FEASIBILITY_HALF_WIDTHS_MM:
        extents = np.full((TARGET_COUNT, 2), half_width_mm, dtype=np.float64)
        _, margins, misses = _score_absolute_target_rectangles(
            tips[:, :, :2], centers[:, :2], extents, np
        )
        target_rows = []
        for index, pose in enumerate(poses):
            miss_count = int(misses[index].sum())
            target_rows.append(
                {
                    "target_id": pose["target_id"],
                    "miss_count": miss_count,
                    "miss_rate_one_sided_95_wilson_upper": _wilson_upper(
                        miss_count, WORLDS_PER_TARGET
                    ),
                    "p01_margin_mm": float(np.quantile(margins[index], 0.01)),
                    "minimum_margin_mm": float(margins[index].min()),
                }
            )
        worst_ucb = max(
            target_rows, key=lambda row: row["miss_rate_one_sided_95_wilson_upper"]
        )
        worst_p01 = min(target_rows, key=lambda row: row["p01_margin_mm"])
        cells.append(
            {
                "effective_safe_half_width_mm": half_width_mm,
                "feasible": all(
                    row["miss_rate_one_sided_95_wilson_upper"] <= MISS_UCB_LIMIT
                    and row["p01_margin_mm"] >= 0.0
                    for row in target_rows
                ),
                "total_misses": sum(row["miss_count"] for row in target_rows),
                "maximum_target_miss_ucb": worst_ucb[
                    "miss_rate_one_sided_95_wilson_upper"
                ],
                "maximum_target_miss_ucb_target_id": worst_ucb["target_id"],
                "minimum_target_p01_margin_mm": worst_p01["p01_margin_mm"],
                "minimum_target_p01_margin_target_id": worst_p01["target_id"],
                "minimum_margin_mm": min(
                    row["minimum_margin_mm"] for row in target_rows
                ),
            }
        )
    return cells


def _apply_cartesian_calibration(
    raw_tips, fixed_cartesian_delta, residual_fraction: float
):
    """Apply a local per-target correction, leaving the declared residual bias."""
    return raw_tips - (1.0 - residual_fraction) * fixed_cartesian_delta[:, None, :]


def _run_feasibility(
    args,
    poses,
    nominal_q,
    centers,
    board_t_world,
    tool_length_mm,
    warp_model,
    warp_data,
    hand_id,
    np,
    mjw,
    wp,
):
    seed = SEED + 2
    rng = np.random.Generator(np.random.PCG64(seed))
    random_unit = rng.normal(
        0.0, 1.0, size=(TARGET_COUNT, WORLDS_PER_TARGET, 5)
    )
    signs = rng.integers(
        0, 2, size=(TARGET_COUNT, WORLDS_PER_TARGET, 5), dtype=np.int8
    )
    backlash_unit = signs.astype(np.float64) * 2.0 - 1.0
    systematic_unit = rng.uniform(-1.0, 1.0, size=(WORLDS_PER_TARGET, 5))
    total_worlds = TARGET_COUNT * WORLDS_PER_TARGET
    scenario_rows = []
    for noise_level in FEASIBILITY_NOISE_LEVELS_RAD:
        for backlash_level in FEASIBILITY_BACKLASH_LEVELS_RAD:
            for systematic_level in FEASIBILITY_SYSTEMATIC_LEVELS_RAD:
                offsets = (
                    random_unit * noise_level
                    + backlash_unit * backlash_level
                    + systematic_unit[None, :, :] * systematic_level
                )
                qpos = np.broadcast_to(
                    nominal_q[:, None, :], (TARGET_COUNT, WORLDS_PER_TARGET, 6)
                ).copy()
                qpos[:, :, :5] += offsets
                if not np.isfinite(qpos).all():
                    raise ValueError("nonfinite combined perturbed joint state")
                warp_data.qpos.assign(qpos.reshape(total_worlds, 6))
                mjw.forward(warp_model, warp_data)
                wp.synchronize_device(wp.get_device())
                tips = _board_tips(
                    warp_data, hand_id, board_t_world, tool_length_mm, np
                ).reshape(TARGET_COUNT, WORLDS_PER_TARGET, 3)
                scenario_rows.append(
                    {
                        "random_joint_noise_sigma_rad": noise_level,
                        "sampled_sign_backlash_magnitude_rad": backlash_level,
                        "campaign_systematic_uniform_half_width_rad": systematic_level,
                        "safe_width_cells": _safe_width_cells(
                            tips, centers, poses, np
                        ),
                    }
                )
    result = {
        "schema": "rocell.mujoco_warp_safe_region_combined_feasibility.v1",
        "status": "PASS_EXPLORATORY_FEASIBILITY_MAP",
        "scope": "SYNTHETIC_UNMEASURED_SYMMETRIC_SAFE_REGION_POINT_TOOL_ONLY",
        "source_sha256": dict(EXPECTED),
        "stack": _stack(args.device),
        "device": args.device,
        "seed": seed,
        "target_count": TARGET_COUNT,
        "worlds_per_target_per_scenario": WORLDS_PER_TARGET,
        "scenario_count": len(scenario_rows),
        "total_forward_kinematic_worlds": len(scenario_rows) * total_worlds,
        "grids": {
            "effective_safe_half_widths_mm": FEASIBILITY_HALF_WIDTHS_MM,
            "random_joint_noise_sigma_rad": FEASIBILITY_NOISE_LEVELS_RAD,
            "sampled_sign_backlash_magnitude_rad": FEASIBILITY_BACKLASH_LEVELS_RAD,
            "campaign_systematic_uniform_half_width_rad": (
                FEASIBILITY_SYSTEMATIC_LEVELS_RAD
            ),
        },
        "scoring": {
            "absolute_target_center_scoring": True,
            "per_scenario_recentering": False,
            "region": "symmetric effective square centered on each catalog target",
            "tool": "zero-radius point tool",
            "candidate_rule": "every target one-sided 95% miss UCB <= 0.001 and p01 margin >= 0",
        },
        "paired_sampling": {
            "random_unit_draws_reused_across_scenarios": True,
            "backlash_signs_reused_across_scenarios": True,
            "systematic_unit_draws_reused_across_scenarios": True,
        },
        "scenarios": scenario_rows,
        "hardware_access": False,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physics_step_count": 0,
        "physical_authority": False,
        "controller_commands": [],
        "limitations": [
            "safe half-widths are a sensitivity axis and are not physical measurements",
            "the point tool omits fingertip radius and deformation",
            "the rank-1 placement and 120 mm tool length are unmeasured",
            "backlash signs are sampled rather than taken from commissioned approach directions",
            "source magnitudes are synthetic and the additive joint-space model is exploratory",
            "no collision, dynamics, servo tracking, contact force, key travel, vision correction, or hardware is modeled",
        ],
    }
    result["receipt_sha256"] = hashlib.sha256(canonical_bytes(result)).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    return result


def _run_calibrated_residual(
    args,
    poses,
    nominal_q,
    centers,
    board_t_world,
    tool_length_mm,
    warp_model,
    warp_data,
    hand_id,
    np,
    mjw,
    wp,
):
    seed = SEED + 3
    rng = np.random.Generator(np.random.PCG64(seed))
    fixed_signs = (
        rng.integers(0, 2, size=(TARGET_COUNT, 5), dtype=np.int8).astype(np.float64)
        * 2.0
        - 1.0
    )
    systematic_unit = rng.uniform(-1.0, 1.0, size=5)
    random_unit = rng.normal(
        0.0, 1.0, size=(TARGET_COUNT, WORLDS_PER_TARGET, 5)
    )
    total_worlds = TARGET_COUNT * WORLDS_PER_TARGET
    scenario_rows = []
    for fixed_magnitude in CALIBRATED_FIXED_SOURCE_MAGNITUDES_RAD:
        fixed_offsets = fixed_signs * fixed_magnitude + systematic_unit * fixed_magnitude
        fixed_q = nominal_q.copy()
        fixed_q[:, :5] += fixed_offsets
        repeated_fixed_q = np.repeat(fixed_q, WORLDS_PER_TARGET, axis=0)
        warp_data.qpos.assign(repeated_fixed_q)
        mjw.forward(warp_model, warp_data)
        wp.synchronize_device(wp.get_device())
        fixed_tips = _board_tips(
            warp_data, hand_id, board_t_world, tool_length_mm, np
        ).reshape(TARGET_COUNT, WORLDS_PER_TARGET, 3)[:, 0, :]
        fixed_cartesian_delta = fixed_tips - centers
        for noise_level in CALIBRATED_RANDOM_LEVELS_RAD:
            qpos = np.broadcast_to(
                fixed_q[:, None, :], (TARGET_COUNT, WORLDS_PER_TARGET, 6)
            ).copy()
            qpos[:, :, :5] += random_unit * noise_level
            warp_data.qpos.assign(qpos.reshape(total_worlds, 6))
            mjw.forward(warp_model, warp_data)
            wp.synchronize_device(wp.get_device())
            raw_tips = _board_tips(
                warp_data, hand_id, board_t_world, tool_length_mm, np
            ).reshape(TARGET_COUNT, WORLDS_PER_TARGET, 3)
            for residual_fraction in CALIBRATED_RESIDUAL_FRACTIONS:
                corrected_tips = _apply_cartesian_calibration(
                    raw_tips, fixed_cartesian_delta, residual_fraction
                )
                scenario_rows.append(
                    {
                        "fixed_backlash_and_systematic_magnitude_rad_each": (
                            fixed_magnitude
                        ),
                        "random_joint_noise_sigma_rad": noise_level,
                        "per_key_calibration_residual_fraction": residual_fraction,
                        "safe_width_cells": _safe_width_cells(
                            corrected_tips,
                            centers,
                            poses,
                            np,
                            CALIBRATED_HALF_WIDTHS_MM,
                        ),
                    }
                )
    result = {
        "schema": "rocell.mujoco_warp_fixed_approach_calibrated_residual.v1",
        "status": "PASS_EXPLORATORY_CALIBRATED_RESIDUAL",
        "scope": "SYNTHETIC_FIXED_APPROACH_LOCAL_CARTESIAN_CORRECTION_POINT_TOOL_ONLY",
        "source_sha256": dict(EXPECTED),
        "stack": _stack(args.device),
        "device": args.device,
        "seed": seed,
        "target_count": TARGET_COUNT,
        "worlds_per_target_per_fk_scenario": WORLDS_PER_TARGET,
        "fk_scenario_count": (
            len(CALIBRATED_FIXED_SOURCE_MAGNITUDES_RAD)
            * (1 + len(CALIBRATED_RANDOM_LEVELS_RAD))
        ),
        "scored_scenario_count": len(scenario_rows),
        "total_forward_kinematic_worlds": (
            len(CALIBRATED_FIXED_SOURCE_MAGNITUDES_RAD)
            * (1 + len(CALIBRATED_RANDOM_LEVELS_RAD))
            * total_worlds
        ),
        "grids": {
            "effective_safe_half_widths_mm": CALIBRATED_HALF_WIDTHS_MM,
            "random_joint_noise_sigma_rad": CALIBRATED_RANDOM_LEVELS_RAD,
            "fixed_backlash_and_systematic_magnitude_rad_each": (
                CALIBRATED_FIXED_SOURCE_MAGNITUDES_RAD
            ),
            "per_key_calibration_residual_fraction": CALIBRATED_RESIDUAL_FRACTIONS,
        },
        "model": {
            "approach_direction": "one deterministic five-joint sign vector per target, fixed across presses",
            "systematic_offset": "one deterministic five-joint vector shared across targets",
            "calibration": "subtract declared fraction of each target's fixed Cartesian tip displacement",
            "random_noise": "zero-mean Gaussian joint perturbation, paired across scenarios",
            "absolute_target_center_scoring": True,
            "per_scenario_recentering": False,
        },
        "scenarios": scenario_rows,
        "hardware_access": False,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physics_step_count": 0,
        "physical_authority": False,
        "controller_commands": [],
        "limitations": [
            "fixed approach signs are synthetic and are not derived from commissioned routes",
            "Cartesian subtraction is a local-equivalent correction, not a rerun of inverse kinematics to a corrected aim point",
            "calibration residual fractions are sensitivity values rather than measured accuracy",
            "safe widths, source magnitudes, rank-1 placement, 120 mm tool, and point footprint are unmeasured",
            "no visual correction, collision, dynamics, contact, servo, or physical qualification is claimed",
        ],
    }
    result["receipt_sha256"] = hashlib.sha256(canonical_bytes(result)).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    return result


def run(args: argparse.Namespace) -> dict[str, Any]:
    for name, expected in EXPECTED.items():
        actual = sha256(getattr(args, name))
        if actual != expected:
            raise ValueError(f"{name} SHA-256 mismatch: {actual}")
    import mujoco
    import mujoco_warp as mjw
    import numpy as np
    import warp as wp

    bundle = json.loads(args.pose_bundle.read_text(encoding="utf-8"))
    profile = json.loads(args.virtual_profile.read_text(encoding="utf-8"))
    _validate_pose_bundle(bundle)
    if profile.get("status") != "UNMEASURED_SENSITIVITY_OVERLAY":
        raise ValueError("virtual profile is no longer an unmeasured overlay")
    poses = bundle["poses"]
    nominal_q = np.asarray([pose["joint_positions_rad"] + [0.0] for pose in poses])
    centers = np.asarray([pose["center_board_mm"] for pose in poses], dtype=np.float64)
    extents = np.asarray(
        [pose["nominal_keycap_half_extent_mm"] for pose in poses], dtype=np.float64
    )
    board_t_world = np.asarray(
        profile["study_input"]["derived_solver_transform"]["matrix_row_major"],
        dtype=np.float64,
    ).reshape(4, 4)
    tool_length_mm = float(profile["study_input"]["route_tool_lengths_mm"]["keyboard"])

    model = mujoco.MjModel.from_xml_path(str(args.mjcf))
    data = mujoco.MjData(model)
    hand_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "hand_tcp")
    if hand_id < 0 or model.nq != 6:
        raise ValueError("MJCF joint/body contract changed")
    wp.init()
    wp.set_device(args.device)
    warp_model = mjw.put_model(model)
    total_worlds = TARGET_COUNT * WORLDS_PER_TARGET
    warp_data = mjw.put_data(model, data, nworld=total_worlds)

    # Standard-MuJoCo nominal tips and local XY Jacobians provide an independent
    # small-noise linearization check for the Warp Monte Carlo path.
    nominal_tips = []
    jacobians = []
    jacobian_conditions = []
    for q in nominal_q:
        data.qpos[:] = q
        mujoco.mj_forward(model, data)
        nominal_tips.append(
            _board_tips_from_mujoco(data, hand_id, board_t_world, tool_length_mm, np)
        )
        columns = []
        for joint_index in range(5):
            plus = q.copy()
            minus = q.copy()
            plus[joint_index] += FINITE_DIFFERENCE_STEP_RAD
            minus[joint_index] -= FINITE_DIFFERENCE_STEP_RAD
            data.qpos[:] = plus
            mujoco.mj_forward(model, data)
            plus_tip = _board_tips_from_mujoco(
                data, hand_id, board_t_world, tool_length_mm, np
            )
            data.qpos[:] = minus
            mujoco.mj_forward(model, data)
            minus_tip = _board_tips_from_mujoco(
                data, hand_id, board_t_world, tool_length_mm, np
            )
            columns.append(
                (plus_tip[:2] - minus_tip[:2]) / (2.0 * FINITE_DIFFERENCE_STEP_RAD)
            )
        jacobian = np.stack(columns, axis=1)
        jacobians.append(jacobian)
        singular = np.linalg.svd(jacobian, compute_uv=False)
        jacobian_conditions.append(float(singular[0] / singular[-1]))
    nominal_tips = np.asarray(nominal_tips)
    jacobians = np.asarray(jacobians)

    if args.mode == "feasibility":
        return _run_feasibility(
            args,
            poses,
            nominal_q,
            centers,
            board_t_world,
            tool_length_mm,
            warp_model,
            warp_data,
            hand_id,
            np,
            mjw,
            wp,
        )

    if args.mode == "calibrated":
        return _run_calibrated_residual(
            args,
            poses,
            nominal_q,
            centers,
            board_t_world,
            tool_length_mm,
            warp_model,
            warp_data,
            hand_id,
            np,
            mjw,
            wp,
        )

    refinement = args.mode == "refinement"
    seed = SEED + (1 if refinement else 0)
    levels_by_source = (
        REFINEMENT_LEVELS_RAD
        if refinement
        else {source: LEVELS_RAD for source in (
            "random_joint_noise",
            "approach_direction_backlash",
            "systematic_calibration_offset",
        )}
    )
    rng = np.random.Generator(np.random.PCG64(seed))
    source_results: dict[str, list[dict[str, Any]]] = {
        "random_joint_noise": [],
        "approach_direction_backlash": [],
        "systematic_calibration_offset": [],
    }
    random_small_empirical_rms = None
    for source_name in source_results:
        for level in levels_by_source[source_name]:
            if source_name == "random_joint_noise":
                offsets = rng.normal(
                    0.0, level, size=(TARGET_COUNT, WORLDS_PER_TARGET, 5)
                )
            elif source_name == "approach_direction_backlash":
                signs = rng.integers(
                    0, 2, size=(TARGET_COUNT, WORLDS_PER_TARGET, 5), dtype=np.int8
                )
                offsets = (signs.astype(np.float64) * 2.0 - 1.0) * level
            else:
                campaign_offsets = rng.uniform(
                    -level, level, size=(WORLDS_PER_TARGET, 5)
                )
                offsets = np.broadcast_to(
                    campaign_offsets[None, :, :],
                    (TARGET_COUNT, WORLDS_PER_TARGET, 5),
                ).copy()
            qpos = np.broadcast_to(
                nominal_q[:, None, :], (TARGET_COUNT, WORLDS_PER_TARGET, 6)
            ).copy()
            qpos[:, :, :5] += offsets
            if not np.isfinite(qpos).all():
                raise ValueError("nonfinite perturbed joint state")
            flat = qpos.reshape(total_worlds, 6)
            warp_data.qpos.assign(flat)
            mjw.forward(warp_model, warp_data)
            wp.synchronize_device(wp.get_device())
            tips = _board_tips(
                warp_data, hand_id, board_t_world, tool_length_mm, np
            ).reshape(TARGET_COUNT, WORLDS_PER_TARGET, 3)
            delta_center, margins, misses = _score_absolute_target_rectangles(
                tips[:, :, :2], centers[:, :2], extents, np
            )
            delta_nominal = tips[:, :, :2] - nominal_tips[:, None, :2]
            target_rows = []
            for index, pose in enumerate(poses):
                miss_count = int(misses[index].sum())
                radial_nominal = np.linalg.norm(delta_nominal[index], axis=1)
                radial_center = np.linalg.norm(delta_center[index], axis=1)
                target_rows.append(
                    {
                        "target_id": pose["target_id"],
                        "miss_count": miss_count,
                        "miss_rate": miss_count / WORLDS_PER_TARGET,
                        "miss_rate_one_sided_95_wilson_upper": _wilson_upper(
                            miss_count, WORLDS_PER_TARGET
                        ),
                        "minimum_margin_mm": float(margins[index].min()),
                        "p01_margin_mm": float(np.quantile(margins[index], 0.01)),
                        "median_margin_mm": float(np.median(margins[index])),
                        "p99_radial_displacement_from_nominal_mm": float(
                            np.quantile(radial_nominal, 0.99)
                        ),
                        "minimum_radial_distance_from_target_center_mm": float(
                            radial_center.min()
                        ),
                        "median_radial_distance_from_target_center_mm": float(
                            np.median(radial_center)
                        ),
                        "p99_radial_distance_from_target_center_mm": float(
                            np.quantile(radial_center, 0.99)
                        ),
                        "maximum_radial_distance_from_target_center_mm": float(
                            radial_center.max()
                        ),
                        "maximum_absolute_x_from_target_center_mm": float(
                            np.abs(delta_center[index, :, 0]).max()
                        ),
                        "maximum_absolute_y_from_target_center_mm": float(
                            np.abs(delta_center[index, :, 1]).max()
                        ),
                    }
                )
            source_results[source_name].append(
                {
                    "level_rad": level,
                    "level_interpretation": {
                        "random_joint_noise": "per-joint Gaussian standard deviation",
                        "approach_direction_backlash": "per-joint signed magnitude with sampled approach-direction surrogate",
                        "systematic_calibration_offset": "per-joint uniform half-width, constant across all targets in one campaign",
                    }[source_name],
                    "all_target_miss_ucb_at_most_0_001": all(
                        row["miss_rate_one_sided_95_wilson_upper"] <= MISS_UCB_LIMIT
                        for row in target_rows
                    ),
                    "all_target_p01_margins_nonnegative": all(
                        row["p01_margin_mm"] >= 0.0 for row in target_rows
                    ),
                    "targets": target_rows,
                }
            )
            if source_name == "random_joint_noise" and level == 0.00025:
                random_small_empirical_rms = np.sqrt(
                    np.mean(np.sum(delta_nominal * delta_nominal, axis=2), axis=1)
                )

    predicted_rms = 0.00025 * np.sqrt(
        np.sum(jacobians * jacobians, axis=(1, 2))
    )
    ratios = random_small_empirical_rms / predicted_rms
    jacobian_rows = [
        {
            "target_id": pose["target_id"],
            "xy_jacobian_condition_number": jacobian_conditions[index],
            "predicted_small_noise_radial_rms_mm": float(predicted_rms[index]),
            "empirical_small_noise_radial_rms_mm": float(
                random_small_empirical_rms[index]
            ),
            "empirical_to_linear_rms_ratio": float(ratios[index]),
        }
        for index, pose in enumerate(poses)
    ]
    candidate_levels = {}
    for source_name, levels in source_results.items():
        admitted = [
            row["level_rad"]
            for row in levels
            if row["all_target_miss_ucb_at_most_0_001"]
            and row["all_target_p01_margins_nonnegative"]
        ]
        largest = max(admitted) if admitted else None
        top_passed = largest == levels_by_source[source_name][-1]
        first_failed = next(
            (row["level_rad"] for row in levels if row["level_rad"] > (largest or -1.0)
             and not (
                 row["all_target_miss_ucb_at_most_0_001"]
                 and row["all_target_p01_margins_nonnegative"]
             )),
            None,
        )
        candidate_levels[source_name] = {
            "largest_tested_passing_level_rad": largest,
            "first_tested_failing_level_rad": first_failed,
            "upper_search_bound_reached_while_passing": top_passed,
            "threshold_identified_within_grid": largest is not None and not top_passed,
        }
    jacobian_gate = bool(
        np.all(ratios >= JACOBIAN_RATIO_RANGE[0])
        and np.all(ratios <= JACOBIAN_RATIO_RANGE[1])
    )
    result: dict[str, Any] = {
        "schema": (
            "rocell.mujoco_warp_nominal_target_uncertainty_refinement.v2"
            if refinement
            else "rocell.mujoco_warp_nominal_target_uncertainty.v1"
        ),
        "status": "PASS_EXPLORATORY_SENSITIVITY" if jacobian_gate else "FAIL_LINEAR_SANITY",
        "scope": "SYNTHETIC_UNMEASURED_NOMINAL_KEYCAP_POINT_TOOL_ONLY",
        "source_sha256": dict(EXPECTED),
        "stack": _stack(args.device),
        "device": args.device,
        "seed": seed,
        "target_count": TARGET_COUNT,
        "worlds_per_target_per_level": WORLDS_PER_TARGET,
        "levels_rad": levels_by_source if refinement else LEVELS_RAD,
        "scoring": {
            "region": "nominal keycap rectangle from current 46-target catalog",
            "tool": "zero-radius point tool",
            "miss": "tool-tip board XY lies outside target rectangle",
            "margin_mm": "minimum signed distance to rectangle X/Y edge",
            "absolute_target_center_scoring": True,
            "per_source_recentering": False,
            "diagnostic_only": "displacement from the unperturbed nominal landing",
            "candidate_rule": "largest tested level with every target one-sided 95% miss UCB <= 0.001 and p01 margin >= 0",
        },
        "error_sources": source_results,
        "provisional_synthetic_threshold_search": candidate_levels,
        "jacobian_sanity": {
            "finite_difference_step_rad": FINITE_DIFFERENCE_STEP_RAD,
            "random_noise_level_rad": 0.00025,
            "accepted_ratio_range": list(JACOBIAN_RATIO_RANGE),
            "all_targets_pass": jacobian_gate,
            "minimum_ratio": float(ratios.min()),
            "maximum_ratio": float(ratios.max()),
            "targets": jacobian_rows,
        },
        "hardware_access": False,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physics_step_count": 0,
        "physical_authority": False,
        "controller_commands": [],
        "limitations": [
            "candidate levels are synthetic planning values, not physical requirements or qualification",
            "key rectangles, rank-1 placement, 120 mm tool, and zero-radius tool footprint are unmeasured",
            "backlash direction is sampled rather than derived from a commissioned approach trajectory",
            "systematic offsets are bounded synthetic draws rather than calibrated joint-zero evidence",
            "no collision, dynamics, servo tracking, contact force, key travel, or hardware is modeled",
        ],
    }
    result["receipt_sha256"] = hashlib.sha256(canonical_bytes(result)).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return result


def _board_tips_from_mujoco(data, hand_id, board_t_world, tool_length_mm, np):
    position = np.asarray(data.xpos[hand_id], dtype=np.float64) * 1000.0
    rotation = np.asarray(data.xmat[hand_id], dtype=np.float64).reshape(3, 3)
    world = position + rotation @ np.asarray([0.0, 0.0, -tool_length_mm])
    return (board_t_world @ np.concatenate((world, [1.0])))[:3]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pose-bundle", type=Path, required=True)
    parser.add_argument("--target-catalog", type=Path, required=True)
    parser.add_argument("--virtual-profile", type=Path, required=True)
    parser.add_argument("--mjcf", type=Path, required=True)
    parser.add_argument("--device", choices=("cuda:0", "cuda:1"), required=True)
    parser.add_argument(
        "--mode",
        choices=("original", "refinement", "feasibility", "calibrated"),
        default="original",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args)
    print(
        json.dumps(
            {
                "status": result["status"],
                "threshold_search": result.get("provisional_synthetic_threshold_search"),
                "jacobian_ratio_range": (
                    [
                        result["jacobian_sanity"]["minimum_ratio"],
                        result["jacobian_sanity"]["maximum_ratio"],
                    ]
                    if "jacobian_sanity" in result
                    else None
                ),
                "scenario_count": result.get("scenario_count"),
            },
            sort_keys=True,
        )
    )
    return 0 if result["status"].startswith("PASS_EXPLORATORY_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
