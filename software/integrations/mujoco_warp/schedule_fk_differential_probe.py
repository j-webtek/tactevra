"""Replay one frozen arm schedule through RoCell, MuJoCo, and MuJoCo Warp.

The retained Isaac receipt proves that the same exact schedule was previously
replayed there.  It contains an all-sample aggregate rather than every Isaac
sample, so this probe reports that limitation instead of inventing pairwise
Isaac values.
"""

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
    "bundle": "4aece6ef7c7194aea59af2263caff6d4a3be65273a5df92348bf796b7103bb8c",
    "isaac_receipt": "3780fd590f912835c85b69d3265291572eca767ab63ab3b859b9dcbbe18b6078",
    "profile": "38b348ace299140e5908cf367fc15f32b33bebe9b064d5efffe5dcf95f7b4634",
    "urdf": "a565718e7d74b07702802cf41eb9549a6e38e50b5e80aa9b887ab1ae3d0d8190",
    "mjcf": "448b711ae30ed3df8a5f5eff66ecb53034f6540eade7264388d86e3911a7a8a0",
    "toolchain_lock": "ed5150e46850b4bffe2486ce6c162209319414daf2cbceb7eed04c7dce9bf650",
}
JOINT_ORDER = [
    "base_link_to_link1",
    "link1_to_link2",
    "link2_to_link3",
    "link3_to_link4",
    "link4_to_link5",
    "link5_to_gripper_link",
]
SAMPLE_COUNT = 133
RUNTIME_MUJOCO_LIMIT_MM = 0.1
WARP_MUJOCO_LIMIT_MM = 0.01
ISAAC_REFERENCE_LIMIT_MM = 0.25


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _require_hash(name: str, path: Path) -> None:
    actual = sha256(path)
    if actual != EXPECTED[name]:
        raise ValueError(f"{name} SHA-256 mismatch: {actual}")


def _host_stack(device_name: str) -> dict[str, Any]:
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
    try:
        selected = gpus[int(device_name.split(":", 1)[1])]
    except (IndexError, ValueError) as exc:
        raise ValueError(f"unavailable CUDA device {device_name}") from exc
    packages = {
        name: importlib.metadata.version(name)
        for name in ("mujoco", "mujoco-warp", "numpy", "warp-lang")
    }
    return {
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "packages": packages,
        "selected_device": {"requested": device_name, **selected},
        "all_gpus": gpus,
        "same_stack_reproducibility": "BITWISE_CANONICAL_RECEIPT",
        "different_stack_reproducibility": "FROZEN_NUMERICAL_TOLERANCES",
    }


def _validate_inputs(
    bundle: dict[str, Any], isaac: dict[str, Any], profile: dict[str, Any]
) -> None:
    if bundle.get("schema") != "tactevra.arm_joint_schedule_replay_bundle.v1":
        raise ValueError("unsupported schedule bundle")
    if bundle.get("sample_count") != SAMPLE_COUNT or len(bundle.get("samples", [])) != SAMPLE_COUNT:
        raise ValueError("schedule must contain exactly 133 samples")
    if [row.get("sequence") for row in bundle["samples"]] != list(range(SAMPLE_COUNT)):
        raise ValueError("schedule order is not exact")
    if bundle.get("scope") != "SYNTHETIC_OFFLINE_ISAAC_REPLAY_ONLY":
        raise ValueError("schedule scope changed")
    if bundle.get("hardware_access") is not False or bundle.get("physical_authority") is not False:
        raise ValueError("schedule carries authority")
    if bundle.get("hardware_writes") != 0 or bundle.get("physical_movements") != 0:
        raise ValueError("schedule records physical activity")
    if isaac.get("schema") != "tactevra.isaac_joint_schedule_replay.v1":
        raise ValueError("unsupported retained Isaac receipt")
    if isaac.get("sample_count") != SAMPLE_COUNT or isaac.get("all_samples_pass") is not True:
        raise ValueError("retained Isaac replay is not admitted")
    if isaac.get("source_bindings", {}).get("bundle_file_sha256") != EXPECTED["bundle"]:
        raise ValueError("retained Isaac receipt uses a different schedule")
    if isaac.get("hardware_access") is not False or isaac.get("physical_authority") is not False:
        raise ValueError("retained Isaac receipt carries authority")
    if isaac.get("hardware_writes") != 0 or isaac.get("physical_movements") != 0:
        raise ValueError("retained Isaac receipt records physical activity")
    if profile.get("status") != "UNMEASURED_SENSITIVITY_OVERLAY":
        raise ValueError("profile is not the frozen synthetic overlay")
    if profile.get("simulation_only") is not True or profile.get("physical_release_effect") != "NONE":
        raise ValueError("profile could claim physical status")
    for row in bundle["samples"]:
        positions = row.get("joint_positions_rad", {})
        if set(positions) != set(JOINT_ORDER[:-1]):
            raise ValueError("schedule joint set changed")
        values = [positions[name] for name in JOINT_ORDER[:-1]]
        expected_tip = row.get("expected_tool_tip_board_mm", [])
        if len(expected_tip) != 3 or not all(
            isinstance(value, (int, float)) and math.isfinite(value)
            for value in values + expected_tip
        ):
            raise ValueError("schedule contains a nonfinite value")


def _board_tip(hand_position_mm, hand_rotation, tool_length_mm: float, board_t_world, np):
    tip_world = hand_position_mm + hand_rotation @ np.asarray(
        [0.0, 0.0, -tool_length_mm], dtype=np.float64
    )
    return (board_t_world @ np.concatenate((tip_world, [1.0])))[:3]


def run_probe(args: argparse.Namespace) -> dict[str, Any]:
    for name in EXPECTED:
        _require_hash(name, getattr(args, name.replace("isaac_receipt", "isaac")))

    import mujoco
    import mujoco_warp as mjw
    import numpy as np
    import warp as wp
    from rocell.geometry import JointPosition, load_urdf

    bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
    isaac = json.loads(args.isaac.read_text(encoding="utf-8"))
    profile = json.loads(args.profile.read_text(encoding="utf-8"))
    lock = json.loads(args.toolchain_lock.read_text(encoding="utf-8"))
    _validate_inputs(bundle, isaac, profile)
    stack = _host_stack(args.device)
    if stack["python_version"] != lock["python_version"]:
        raise ValueError("Python version differs from toolchain lock")
    if stack["packages"] != {
        name: lock["packages"][name]
        for name in ("mujoco", "mujoco-warp", "numpy", "warp-lang")
    }:
        raise ValueError("simulator package versions differ from toolchain lock")
    selected = stack["selected_device"]
    if selected["uuid"] not in lock["host"]["gpu_uuids"]:
        raise ValueError("selected GPU is not in the toolchain lock")
    if selected["driver_version"] != lock["host"]["driver_version"]:
        raise ValueError("driver version differs from toolchain lock")

    board_t_world = np.asarray(
        profile["study_input"]["derived_solver_transform"]["matrix_row_major"],
        dtype=np.float64,
    ).reshape(4, 4)
    tool_length_mm = float(profile["study_input"]["route_tool_lengths_mm"]["keyboard"])
    qpos = np.asarray(
        [
            [row["joint_positions_rad"].get(name, 0.0) for name in JOINT_ORDER]
            for row in bundle["samples"]
        ],
        dtype=np.float64,
    )

    rocell_model = load_urdf(args.urdf)
    mujoco_model = mujoco.MjModel.from_xml_path(str(args.mjcf))
    mujoco_data = mujoco.MjData(mujoco_model)
    hand_id = mujoco.mj_name2id(mujoco_model, mujoco.mjtObj.mjOBJ_BODY, "hand_tcp")
    if hand_id < 0:
        raise ValueError("MJCF lacks hand_tcp")

    rocell_tips = []
    mujoco_tips = []
    for values in qpos:
        transforms = rocell_model.forward_kinematics(
            {
                name: JointPosition.radians(float(value))
                for name, value in zip(JOINT_ORDER, values, strict=True)
            }
        )
        hand = transforms["hand_tcp"]
        rocell_tips.append(
            _board_tip(
                np.asarray(
                    [
                        hand.translation_mm.x,
                        hand.translation_mm.y,
                        hand.translation_mm.z,
                    ],
                    dtype=np.float64,
                ),
                np.asarray(hand.rotation.matrix, dtype=np.float64).reshape(3, 3),
                tool_length_mm,
                board_t_world,
                np,
            )
        )
        mujoco_data.qpos[:] = values
        mujoco.mj_forward(mujoco_model, mujoco_data)
        mujoco_tips.append(
            _board_tip(
                np.asarray(mujoco_data.xpos[hand_id], dtype=np.float64) * 1000.0,
                np.asarray(mujoco_data.xmat[hand_id], dtype=np.float64).reshape(3, 3),
                tool_length_mm,
                board_t_world,
                np,
            )
        )
    rocell_tips = np.asarray(rocell_tips)
    mujoco_tips = np.asarray(mujoco_tips)

    wp.init()
    wp.set_device(args.device)
    warp_model = mjw.put_model(mujoco_model)
    warp_data = mjw.put_data(mujoco_model, mujoco_data, nworld=SAMPLE_COUNT)
    warp_data.qpos.assign(qpos)
    mjw.forward(warp_model, warp_data)
    wp.synchronize_device(wp.get_device())
    warp_positions = np.asarray(warp_data.xpos.numpy(), dtype=np.float64)[:, hand_id, :] * 1000.0
    warp_rotations = np.asarray(warp_data.xmat.numpy(), dtype=np.float64)[:, hand_id, :, :]
    warp_tips = np.asarray(
        [
            _board_tip(position, rotation, tool_length_mm, board_t_world, np)
            for position, rotation in zip(warp_positions, warp_rotations, strict=True)
        ]
    )

    schedule_reference = np.asarray(
        [row["expected_tool_tip_board_mm"] for row in bundle["samples"]],
        dtype=np.float64,
    )
    schedule_vs_rocell = np.linalg.norm(schedule_reference - rocell_tips, axis=1)
    mujoco_vs_rocell = np.linalg.norm(mujoco_tips - rocell_tips, axis=1)
    warp_vs_mujoco = np.linalg.norm(warp_tips - mujoco_tips, axis=1)
    rows = []
    for index, source in enumerate(bundle["samples"]):
        rows.append(
            {
                "sequence": index,
                "phase": source["phase"],
                "target_id": source["target_id"],
                "joint_positions_rad": qpos[index].tolist(),
                "schedule_reference_tip_board_mm": schedule_reference[index].tolist(),
                "rocell_tip_board_mm": rocell_tips[index].tolist(),
                "mujoco_tip_board_mm": mujoco_tips[index].tolist(),
                "mujoco_warp_tip_board_mm": warp_tips[index].tolist(),
                "schedule_reference_vs_rocell_mm": float(schedule_vs_rocell[index]),
                "mujoco_vs_rocell_mm": float(mujoco_vs_rocell[index]),
                "mujoco_warp_vs_mujoco_mm": float(warp_vs_mujoco[index]),
            }
        )
    metrics = {
        "maximum_schedule_reference_vs_rocell_mm": float(schedule_vs_rocell.max()),
        "maximum_mujoco_vs_rocell_mm": float(mujoco_vs_rocell.max()),
        "maximum_mujoco_warp_vs_mujoco_mm": float(warp_vs_mujoco.max()),
        "retained_isaac_maximum_vs_schedule_reference_mm": float(
            isaac["maximum_tool_tip_error_mm"]
        ),
    }
    gates = {
        "all_samples_present_ordered_finite": bool(
            len(rows) == SAMPLE_COUNT
            and np.isfinite(rocell_tips).all()
            and np.isfinite(mujoco_tips).all()
            and np.isfinite(warp_tips).all()
        ),
        "mujoco_vs_rocell": metrics["maximum_mujoco_vs_rocell_mm"]
        <= RUNTIME_MUJOCO_LIMIT_MM,
        "mujoco_warp_vs_mujoco": metrics["maximum_mujoco_warp_vs_mujoco_mm"]
        <= WARP_MUJOCO_LIMIT_MM,
        "retained_isaac_vs_reference": metrics[
            "retained_isaac_maximum_vs_schedule_reference_mm"
        ]
        <= ISAAC_REFERENCE_LIMIT_MM,
    }
    result: dict[str, Any] = {
        "schema": "rocell.mujoco_warp_schedule_fk_differential.v1",
        "status": "PASS_KINEMATIC_ONLY" if all(gates.values()) else "FAIL",
        "scope": "SYNTHETIC_OFFLINE_SCHEDULE_FK_DIFFERENTIAL_ONLY",
        "source_sha256": dict(EXPECTED),
        "schedule_bundle_sha256": bundle["bundle_sha256"],
        "sample_count": SAMPLE_COUNT,
        "joint_order": JOINT_ORDER,
        "stack": stack,
        "thresholds": {
            "mujoco_vs_rocell_mm": RUNTIME_MUJOCO_LIMIT_MM,
            "mujoco_warp_vs_mujoco_mm": WARP_MUJOCO_LIMIT_MM,
            "retained_isaac_vs_schedule_reference_mm": ISAAC_REFERENCE_LIMIT_MM,
        },
        "metrics": metrics,
        "gates": gates,
        "rows": rows,
        "hardware_access": False,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
        "controller_commands": [],
        "limitations": [
            "governed meshless URDF with placeholder MJCF inertia supports kinematics only",
            "schedule geometry and tool length are an unmeasured simulation-only overlay",
            "retained Isaac receipt reports an all-sample maximum but omits non-contact per-sample tips",
            "no uncertainty qualification, silhouette dilation, collision, dynamics, contact, or rendering claim",
            "same-stack bitwise reproducibility applies only to canonical receipt bytes from this exact stack",
            "different stacks must be compared using frozen numerical tolerances",
        ],
    }
    result["receipt_sha256"] = canonical_sha256(result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--isaac", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--urdf", type=Path, required=True)
    parser.add_argument("--mjcf", type=Path, required=True)
    parser.add_argument("--toolchain-lock", type=Path, required=True)
    parser.add_argument("--device", choices=("cuda:0", "cuda:1"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_probe(args)
    print(
        json.dumps(
            {
                "status": result["status"],
                "receipt_sha256": result["receipt_sha256"],
                "metrics": result["metrics"],
            },
            sort_keys=True,
        )
    )
    return 0 if result["status"] == "PASS_KINEMATIC_ONLY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
